require 'rails_helper'

RSpec.describe Trophy, type: :model do
  it "is valid if all required fields are filled out and valid" do
    trophy = Trophy.new(
      bjcp_score: 25,
      competition: create(:competition),
      subcategory: Subcategory.last,
      user: create(:user)
    )

    expect(trophy).to be_valid
  end

  it "is valid if all required and optional fields are filled out and valid" do
    trophy = Trophy.new(
      bjcp_score: 25,
      competition: create(:competition),
      place: 1,
      place_context: "category",
      subcategory: Subcategory.last,
      recipe_url: "http://iancanderson.com/brewlog/batches/001",
      user: create(:user)
    )

    expect(trophy).to be_valid
  end

  describe "#leaderboard_score" do
    # 3, 2, 1, 0.5 for 1st, 2nd, 3rd, HM in category respectively
    # plus a bonus 3, 2, 1, 0.5 for BOS places
    # bonus 0.5 for a high-profile competition

    it "returns 3 for category 1st" do
      trophy = build(:trophy, :category_1st)
      expect(trophy.leaderboard_score).to eq 3
    end

    it "returns 2 for category 2nd" do
      trophy = build(:trophy, :category_2nd)
      expect(trophy.leaderboard_score).to eq 2
    end

    it "returns 1 for category 3rd" do
      trophy = build(:trophy, :category_3rd)
      expect(trophy.leaderboard_score).to eq 1
    end

    it "returns 0.5 for category HM" do
      trophy = build(:trophy, :category_hm)
      expect(trophy.leaderboard_score).to eq 0.5
    end

    it "doubles the score for BOS places" do
      trophy = build(:trophy, :best_of_show_3rd)
      expect(trophy.leaderboard_score).to eq 2
    end

    it "adds a 0.5 bonus for a high-profile competition" do
      comp = build(:competition, :high_profile)
      trophy = build(:trophy, :best_of_show_3rd, competition: comp)
      expect(trophy.leaderboard_score).to eq 2.5
    end
  end
end

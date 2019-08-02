require "rails_helper"

describe Season do
  describe ".for_date" do
    it "returns the previous and current year if before July 1" do
      expect(Season.for_date(Date.parse("2018-05-19"))).to eq Season.new(2017, 2018)
    end

    it "returns the current year and next year if after June 30" do
      expect(Season.for_date(Date.parse("2018-07-19"))).to eq Season.new(2018, 2019)
    end
  end

  describe "#previous" do
    it "returns the previous season" do
      current_season = Season.new(2019, 2020)

      expect(current_season.previous).to eq Season.new(2018, 2019)
    end
  end
end

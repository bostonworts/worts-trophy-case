require "rails_helper"

describe Competition do
  describe ".years_descending" do
    it "returns the distinct years for which there are competitions, descending" do
      create(:competition, date: Time.utc("2016-01-01"))
      create(:competition, date: Time.utc("2016-01-01"))
      create(:competition, date: Time.utc("2018-01-01"))
      create(:competition, date: Time.utc("2017-01-01"))

      expect(Competition.years_descending).to eq([2018, 2017, 2016])
    end
  end
end

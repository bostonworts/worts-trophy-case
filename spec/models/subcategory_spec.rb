require 'rails_helper'

RSpec.describe Subcategory, type: :model do
  describe ".sorted" do
    it "sorts 10A after 2A" do
      bjcp_ids = Subcategory.sorted.map(&:bjcp_id)

      expect(bjcp_ids.index("10A")).to be > bjcp_ids.index("2A")
    end

    it "sorts M3B after 10A" do
      bjcp_ids = Subcategory.sorted.map(&:bjcp_id)

      expect(bjcp_ids.index("M3B")).to be > bjcp_ids.index("10A")
    end
  end
end
